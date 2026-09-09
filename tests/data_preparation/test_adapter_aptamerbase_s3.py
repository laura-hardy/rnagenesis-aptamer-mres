"""Tests for the AptamerBase S3 eligibility adapter (synthetic only).

Every literal nucleotide string is a runtime-built ACGU/ACGT tile.
Does not read or embed real AptamerBase sequences.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb_s3 import PLAN_REJECTION_REASONS as APTADB_PLAN_REJECTION  # noqa: E402
from adapters.aptaindex_s3 import (  # noqa: E402
    PLAN_REJECTION_REASONS as APTAINDEX_PLAN_REJECTION,
)
from adapters.aptamerbase import (  # noqa: E402
    TYPE_APTAMER,
    TYPE_PREDICTED_STRUCTURE,
    TYPE_SECONDARY_STRUCTURE,
)
from adapters.aptamerbase_s3 import (  # noqa: E402
    PLAN_REJECTION_REASONS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    AptamerBaseS3Error,
    apply_random_accept_audit,
    classify_aptamerbase_record,
    index_constant_proposals,
)
from adapters.riboaptamer_s3 import (  # noqa: E402
    PLAN_REJECTION_REASONS as RIBO_PLAN_REJECTION,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import (  # noqa: E402
    EligibilityDecision,
    EligibilityReason,
    load_eligibility_policy,
)

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "aptamerbase.json"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _dna(n: int) -> str:
    return ("ACGT" * ((n // 4) + 1))[:n]


def _s2(
    *,
    sequence: str,
    molecule_type: str = "RNA",
    chemistry: str = "RNA",
    alphabet: str = "RNA",
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
    trim_confidence: str = "n/a",
    native_id: str = "0001",
    **overrides: str,
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"aptamerbase:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "trim_confidence": trim_confidence,
            "molecule_type": molecule_type if sequence else "unknown",
            "alphabet_as_reported": alphabet if sequence else "missing",
            "t_to_u_applied": "false",
            "chemistry": chemistry if sequence else "unknown",
            "target_name_raw": "",
            "source_db": "aptamerbase",
            "source_dataset": "aptamerbase_export_2026-06-24",
            "contributing_sources": "aptamerbase",
            "contributing_datasets": "aptamerbase_export_2026-06-24",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "publication": "Demo",
            "qc_flags": qc_flags,
        }
    )
    record.update(overrides)
    return record


def _qc(
    canonical: dict[str, str],
    *,
    source_object_type: str = "aptamer",
    chemistry_class: str = "unmodified_backbone",
    rdf_has_rna: str = "true",
    rdf_has_dna: str = "false",
    rdf_has_modified_nucleic_acid: str = "false",
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamerbase_id": canonical["native_id"],
        "source_object_type": source_object_type,
        "target_name_raw": "",
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "chemistry_class": chemistry_class,
        "molecule_evidence_source": "rdf",
        "t_to_u_applied": canonical["t_to_u_applied"],
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "reported_length_raw": canonical["sequence_length_core"],
        "length_matches_source": "true",
        "observable_length_bucket": "",
        "rdf_has_rna": rdf_has_rna,
        "rdf_has_dna": rdf_has_dna,
        "rdf_has_modified_nucleic_acid": rdf_has_modified_nucleic_acid,
        "rdf_has_minimal_aptamer_type": "false",
        "has_minimal_aptamer_sidecar": "false",
        "is_minimal_aptamer_of_sidecar": "false",
        "modification_text_present": "false",
        "detected_motifs": "",
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical["trim_confidence"],
        "qc_flags": canonical["qc_flags"],
        "review_reasons": "",
    }


def _meta(
    canonical: dict[str, str],
    *,
    aptamerbase_type: str = TYPE_APTAMER,
    aptamerbase_id: str | None = None,
    **overrides: str,
) -> dict[str, str]:
    row = {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamerbase_csv_data_row": "1",
        "aptamerbase_type": aptamerbase_type,
        "aptamerbase_id": aptamerbase_id or canonical["native_id"],
        "aptamerbase_label": f"label-{canonical['native_id']}",
        "aptamerbase_sequence": canonical["sequence_raw"],
        "aptamerbase_sequence_length": canonical["sequence_length_core"],
        "aptamerbase_has_mutational_analysis": "",
        "aptamerbase_has_experimentally_determined_structure": "",
        "aptamerbase_has_minimal_aptamer": "",
        "aptamerbase_is_minimal_aptamer_of": "",
        "aptamerbase_has_application": "",
        "aptamerbase_has_modification_details": "",
        "aptamerbase_has_secondary_structure": "",
        "aptamerbase_has_predicted_secondary_structure": "",
        "aptamerbase_has_sequence_pattern": "",
    }
    row.update(overrides)
    return row


def _classify(
    canonical: dict[str, str],
    *,
    source_object_type: str = "aptamer",
    aptamerbase_type: str = TYPE_APTAMER,
    chemistry_class: str = "unmodified_backbone",
    rdf_has_rna: str = "true",
    rdf_has_dna: str = "false",
    rdf_has_modified_nucleic_acid: str = "false",
    proposals: list[dict[str, str]] | None = None,
    **meta: str,
):
    return classify_aptamerbase_record(
        canonical,
        _qc(
            canonical,
            source_object_type=source_object_type,
            chemistry_class=chemistry_class,
            rdf_has_rna=rdf_has_rna,
            rdf_has_dna=rdf_has_dna,
            rdf_has_modified_nucleic_acid=rdf_has_modified_nucleic_acid,
        ),
        _meta(canonical, aptamerbase_type=aptamerbase_type, **meta),
        policy=POLICY,
        proposals=proposals or (),
    )


def _known_motif(record_id: str) -> dict[str, str]:
    return {
        "proposal_id": f"{record_id}:known_motif:five_prime:t7_promoter_minimal",
        "experiment_group_id": record_id,
        "proposal_source": "known_motif",
        "side": "five_prime",
        "proposed_sequence": "",
        "motif_id": "t7_promoter_minimal",
        "motif_length": "18",
        "support": "",
        "records_considered": "1",
        "records_matching_exactly": "1",
        "confidence": "configured_motif_library",
        "status": "proposed_for_review",
        "applied": "false",
        "reason_not_applied": "detection_only_not_an_approved_trim",
        "reason": "known_motif:t7_promoter_minimal",
    }


def test_policy_defers_target_evidence_leakage() -> None:
    assert POLICY.defer_target_classification is True
    assert POLICY.defer_evidence_scoring is True
    assert POLICY.defer_leakage_exclusion is True
    assert POLICY.unresolved_trim_blocks_eligibility is True
    assert POLICY.random_accept_audit_size == 30
    assert POLICY.random_seed == 42


def test_secondary_structure_object_is_non_aptamer_reject() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="s1", molecule_type="unknown", chemistry="unknown"),
        source_object_type="nucleic_acid_secondary_structure",
        aptamerbase_type=TYPE_SECONDARY_STRUCTURE,
        rdf_has_rna="false",
        chemistry_class="",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.NON_APTAMER_SOURCE_OBJECT
    assert result.primary_route == PRIMARY_ROUTE_REJECT
    assert result.eligibility.manual_review_required is False
    assert result.decision["review_batch"] == ""
    assert result.rejection_row is not None
    assert result.rejection_row["rejection_reason"] == "non_aptamer_source_object"
    assert result.rejection_row["source_object_type"] == (
        "nucleic_acid_secondary_structure"
    )


def test_predicted_structure_with_incidental_rdf_rna_is_still_non_aptamer() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="s2", molecule_type="RNA", chemistry="RNA"),
        source_object_type="predicted_secondary_structure",
        aptamerbase_type=TYPE_PREDICTED_STRUCTURE,
        rdf_has_rna="true",
    )
    assert result.eligibility.primary_reason == EligibilityReason.NON_APTAMER_SOURCE_OBJECT
    assert result.eligibility.manual_review_required is False
    assert result.canonical["molecule_type"] == "RNA"


def test_sequence_bearing_structure_topic_still_rejects_as_non_aptamer() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="s3",
            molecule_type="unknown",
            chemistry="unknown",
            qc_flags="non_aptamer_structure_topic",
        ),
        source_object_type="nucleic_acid_secondary_structure",
        aptamerbase_type=TYPE_SECONDARY_STRUCTURE,
    )
    assert result.eligibility.primary_reason == EligibilityReason.NON_APTAMER_SOURCE_OBJECT
    assert result.eligibility.manual_review_required is False


def test_missing_aptamer_sequence_is_automatic_reject_not_review() -> None:
    result = _classify(
        _s2(sequence="", native_id="m1", qc_flags="missing_sequence"),
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    assert result.eligibility.manual_review_required is False
    assert result.decision["review_batch"] == ""
    assert result.rejection_row is not None
    assert result.rejection_row["rejection_reason"] == "missing_sequence"


def test_structure_missing_sequence_keeps_non_aptamer_primary() -> None:
    result = _classify(
        _s2(sequence="", native_id="m2", qc_flags="missing_sequence|non_aptamer_structure_topic"),
        source_object_type="nucleic_acid_secondary_structure",
        aptamerbase_type=TYPE_SECONDARY_STRUCTURE,
    )
    assert result.eligibility.primary_reason == EligibilityReason.NON_APTAMER_SOURCE_OBJECT
    assert EligibilityReason.MISSING_SEQUENCE in result.eligibility.secondary_reasons
    assert result.eligibility.manual_review_required is False


def test_mixed_t_u_is_technical_reject_with_active_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(20) + "T" + _rna(19),
            native_id="x1",
            alphabet="mixed_T_U",
            qc_flags="mixed_t_u",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.MIXED_T_AND_U
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_sequence_or_source_conflict"
    assert "sequence_notation" in result.decision["checkpoint_review_reasons"]
    assert result.canonical["molecule_type"] == "RNA"


def test_ambiguous_is_technical_reject_with_active_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(20) + "N" + _rna(19),
            native_id="x2",
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
        )
    )
    assert result.eligibility.primary_reason == EligibilityReason.AMBIGUOUS_BASES
    assert result.eligibility.manual_review_required is True
    assert result.canonical["molecule_type"] == "RNA"


def test_invalid_is_technical_reject_with_active_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(20) + "X" + _rna(19),
            native_id="x3",
            alphabet="invalid",
            qc_flags="invalid_character",
        )
    )
    assert result.eligibility.primary_reason == EligibilityReason.INVALID_ALPHABET
    assert result.eligibility.manual_review_required is True
    assert result.canonical["molecule_type"] == "RNA"


def test_alignment_gap_is_technical_reject_with_active_review() -> None:
    gapped = _rna(20) + "-" + _rna(19)
    result = _classify(_s2(sequence=gapped, native_id="x4", alphabet="RNA"))
    assert result.eligibility.primary_reason == EligibilityReason.ALIGNMENT_GAPS
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_sequence_or_source_conflict"


def test_syntax_reject_preserves_explicit_rdf_molecule_type() -> None:
    result = _classify(
        _s2(
            sequence=_rna(20) + "X" + _rna(19),
            native_id="x5",
            alphabet="invalid",
            qc_flags="invalid_character",
            molecule_type="RNA",
        )
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.eligibility.primary_reason != EligibilityReason.MOLECULE_TYPE_UNRESOLVED


def test_actual_length_checked_without_s2_length_qc_flag() -> None:
    short = _s2(sequence=_rna(19), native_id="l1")
    assert "core_below_min_length" not in short["qc_flags"]
    result = _classify(short)
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.manual_review_required is False


def test_invalid_short_row_still_records_length_as_secondary() -> None:
    short_invalid = _s2(
        sequence="ACGX",
        native_id="l2",
        alphabet="invalid",
        qc_flags="invalid_character",
    )
    assert "core_below_min_length" not in short_invalid["qc_flags"]
    result = _classify(short_invalid)
    assert result.eligibility.primary_reason == EligibilityReason.INVALID_ALPHABET
    assert EligibilityReason.LENGTH_OUT_OF_RANGE in result.eligibility.secondary_reasons
    assert result.eligibility.manual_review_required is True


def test_length_above_100_is_out_of_range() -> None:
    result = _classify(_s2(sequence=_rna(101), native_id="l3"))
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.manual_review_required is False


def test_length_plus_notation_uses_syntax_precedence() -> None:
    result = _classify(
        _s2(
            sequence=_rna(10) + "T" + _rna(8),
            native_id="l4",
            alphabet="mixed_T_U",
            qc_flags="mixed_t_u",
        )
    )
    assert result.eligibility.primary_reason == EligibilityReason.MIXED_T_AND_U
    assert EligibilityReason.LENGTH_OUT_OF_RANGE in result.eligibility.secondary_reasons


def test_clean_ssdna_is_parked_not_reviewed() -> None:
    result = _classify(
        _s2(
            sequence=_dna(40),
            native_id="d1",
            molecule_type="ssDNA",
            chemistry="DNA",
            alphabet="DNA_T",
        ),
        rdf_has_rna="false",
        rdf_has_dna="true",
        chemistry_class="unmodified_backbone",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.SSDNA_PARKED
    assert result.primary_route == PRIMARY_ROUTE_SSDNA
    assert result.eligibility.manual_review_required is False
    assert result.canonical["t_to_u_applied"] == "false"
    assert "T" in result.canonical["sequence_core"]
    assert result.park_row is not None


def test_ordinary_ssdna_boundary_length_is_not_active_review() -> None:
    result = _classify(
        _s2(
            sequence=_dna(22),
            native_id="d1b",
            molecule_type="ssDNA",
            chemistry="DNA",
            alphabet="DNA_T",
        ),
        rdf_has_rna="false",
        rdf_has_dna="true",
    )
    assert result.eligibility.primary_reason == EligibilityReason.SSDNA_PARKED
    assert result.eligibility.manual_review_required is False
    assert result.decision["review_batch"] == ""
    assert "length_boundary" not in result.decision["checkpoint_review_reasons"]


def test_ssdna_u_conflict_remains_ssdna_park_but_enters_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="d2",
            molecule_type="ssDNA",
            chemistry="DNA",
            alphabet="RNA",
            qc_flags="source_molecule_alphabet_conflict",
        ),
        rdf_has_rna="false",
        rdf_has_dna="true",
    )
    assert result.eligibility.primary_reason == EligibilityReason.SSDNA_PARKED
    assert result.primary_route == PRIMARY_ROUTE_SSDNA
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_sequence_or_source_conflict"
    assert "source_molecule_alphabet_conflict" in result.decision[
        "checkpoint_review_reasons"
    ]


def test_molecule_unknown_is_parked_for_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="u1",
            molecule_type="unknown",
            chemistry="unknown",
            alphabet="RNA",
        ),
        rdf_has_rna="false",
        rdf_has_dna="false",
        chemistry_class="",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    assert result.primary_route == PRIMARY_ROUTE_MOLECULE
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "02_molecule_type_unresolved"


def test_u_alphabet_does_not_rescue_unknown_molecule() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="u2",
            molecule_type="unknown",
            chemistry="unknown",
            alphabet="RNA",
        )
    )
    assert result.eligibility.primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    assert result.eligibility.primary_reason != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    assert result.canonical["molecule_type"] == "unknown"


def test_straightforward_rna_is_eligible() -> None:
    result = _classify(_s2(sequence=_rna(40), native_id="r1"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.eligibility.primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert result.canonical["target_name_raw"] == ""
    for field_name in S3_FORBIDDEN_FIELDS:
        assert result.canonical.get(field_name, "") == ""


def test_straightforward_2f_rna_is_eligible() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="r2", chemistry="2F-RNA"),
        chemistry_class="twof_rna",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.canonical["chemistry"] == "2F-RNA"


@pytest.mark.parametrize(
    ("chemistry", "native_id"),
    [
        ("2NH2-RNA", "r3"),
        ("2OMe-RNA", "r4"),
        ("mixed", "r5"),
    ],
)
def test_reviewed_modified_rna_chemistries_are_technically_eligible(
    chemistry: str, native_id: str
) -> None:
    """AptamerBase-specific CHECKPOINT-1 reviewed chemistry eligibility."""
    result = _classify(
        _s2(sequence=_rna(40), native_id=native_id, chemistry=chemistry),
        chemistry_class="reviewed_modified_rna",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert result.canonical["chemistry"] == chemistry
    assert result.canonical["molecule_type"] == "RNA"


def test_applied_known_motif_trim_does_not_remain_construct_park() -> None:
    canonical = _s2(
        sequence=_rna(40),
        native_id="k0",
        trim_status="t7_removed",
        trim_confidence="high",
    )
    result = _classify(canonical, proposals=[_known_motif(canonical["record_id"])])
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED not in result.eligibility.all_reasons


def test_rna_unknown_chemistry_is_parked_for_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="c1",
            chemistry="unknown",
        ),
        chemistry_class="2ome",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.CHEMISTRY_REQUIRES_REVIEW
    assert result.primary_route == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "03_chemistry_review"


def test_spiegelmer_is_chemistry_park_not_ordinary_rna() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="c2",
            chemistry="unknown",
            qc_flags="spiegelmer_l_rna_review",
        ),
        chemistry_class="spiegelmer_l_rna",
    )
    assert result.eligibility.primary_reason == EligibilityReason.CHEMISTRY_REQUIRES_REVIEW
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "unknown"
    assert "spiegelmer_l_rna" in result.decision["checkpoint_review_reasons"]
    assert result.eligibility.manual_review_required is True


def test_ssdna_takes_parking_precedence_over_chemistry() -> None:
    result = _classify(
        _s2(
            sequence=_dna(40),
            native_id="c3",
            molecule_type="ssDNA",
            chemistry="unknown",
            alphabet="DNA_T",
        ),
        rdf_has_dna="true",
        rdf_has_rna="false",
        chemistry_class="2ome",
    )
    assert result.eligibility.primary_reason == EligibilityReason.SSDNA_PARKED
    assert EligibilityReason.CHEMISTRY_REQUIRES_REVIEW not in result.eligibility.all_reasons
    assert result.eligibility.manual_review_required is False


def test_modified_type_text_inconsistency_alone_does_not_change_route() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="c4",
            qc_flags="rdf_modified_type_without_modification_text",
        ),
        rdf_has_modified_nucleic_acid="true",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE


def test_known_motif_never_auto_trims() -> None:
    canonical = _s2(sequence=_rna(40), native_id="k1")
    result = _classify(canonical, proposals=[_known_motif(canonical["record_id"])])
    assert result.canonical["sequence_core"] == canonical["sequence_core"]
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["trim_status"] == canonical["trim_status"]


def test_clean_rna_with_unresolved_known_motif_is_construct_park() -> None:
    canonical = _s2(sequence=_rna(40), native_id="k2")
    result = _classify(canonical, proposals=[_known_motif(canonical["record_id"])])
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED
    assert result.primary_route == PRIMARY_ROUTE_CONSTRUCT
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "04_known_motif_construct"
    assert "constant_region_proposal" in result.decision["checkpoint_review_reasons"]


def test_stronger_technical_route_retains_motif_as_secondary() -> None:
    canonical = _s2(
        sequence=_rna(20) + "X" + _rna(19),
        native_id="k3",
        alphabet="invalid",
        qc_flags="invalid_character",
    )
    result = _classify(canonical, proposals=[_known_motif(canonical["record_id"])])
    assert result.eligibility.primary_reason == EligibilityReason.INVALID_ALPHABET
    assert EligibilityReason.KNOWN_MOTIF_PROPOSAL in result.eligibility.secondary_reasons
    assert result.eligibility.manual_review_required is True
    assert "constant_region_proposal" in result.decision["checkpoint_review_reasons"]


def test_length_reject_with_known_motif_enters_construct_review() -> None:
    canonical = _s2(sequence=_rna(19), native_id="k4")
    result = _classify(canonical, proposals=[_known_motif(canonical["record_id"])])
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "04_known_motif_construct"
    assert "constant_region_proposal" in result.decision["checkpoint_review_reasons"]


def test_group_consensus_proposals_are_forbidden() -> None:
    with pytest.raises(AptamerBaseS3Error, match="group_consensus"):
        index_constant_proposals(
            [_s2(sequence=_rna(40), native_id="k5")],
            [
                {
                    "proposal_id": "x",
                    "experiment_group_id": "aptamerbase:k5",
                    "proposal_source": "group_consensus",
                }
            ],
        )


def test_boundary_rows_remain_proposed_accepts() -> None:
    low = _classify(_s2(sequence=_rna(22), native_id="b1"))
    high = _classify(_s2(sequence=_rna(95), native_id="b2"))
    for result in (low, high):
        assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
        assert result.eligibility.manual_review_required is True
        assert result.decision["review_batch"] == "05_accept_with_diagnostics"
        assert result.decision["checkpoint_review_reasons"] == "length_boundary"


def test_deterministic_random_kept_audit() -> None:
    rows = []
    details = {}
    for index in range(8):
        native = f"a{index:02d}"
        classified = _classify(_s2(sequence=_rna(40), native_id=native))
        rows.append(classified.decision)
        details[classified.decision["record_id"]] = {
            "secondary_reasons": classified.decision["secondary_reasons"],
            "checkpoint_review_reasons": classified.decision["checkpoint_review_reasons"],
            "manual_review_required": classified.decision["manual_review_required"],
            "manual_review_priority": classified.decision["manual_review_priority"],
            "review_batch": classified.decision["review_batch"],
        }
    first = [dict(row) for row in rows]
    take, pool, shortfall = apply_random_accept_audit(
        first, details, seed=42, sample_size=3
    )
    assert pool == 8
    assert take == 3
    assert shortfall == 0
    sampled = {
        row["record_id"]
        for row in first
        if "random_accept_audit" in row["secondary_reasons"]
    }
    assert len(sampled) == 3
    second = [dict(row) for row in rows]
    apply_random_accept_audit(second, {}, seed=42, sample_size=3)
    sampled_second = {
        row["record_id"]
        for row in second
        if "random_accept_audit" in row["secondary_reasons"]
    }
    assert sampled == sampled_second
    for row in first:
        if row["record_id"] in sampled:
            assert row["review_batch"] == "06_random_kept_audit"
            assert row["manual_review_required"] == "true"


def test_one_primary_review_row_per_record_and_human_fields_blank() -> None:
    result = _classify(
        _s2(
            sequence=_rna(22),
            native_id="h1",
            chemistry="unknown",
            qc_flags="spiegelmer_l_rna_review",
        ),
        chemistry_class="spiegelmer_l_rna",
        proposals=[_known_motif("aptamerbase:h1")],
    )
    assert result.decision["record_id"] == "aptamerbase:h1"
    assert result.decision["review_batch"] == "03_chemistry_review"
    assert result.decision.get("manual_decision", "") == ""
    from adapters.aptamerbase_s3 import build_local_detail_row

    detail = build_local_detail_row(
        canonical=result.canonical,
        s2_qc=_qc(result.canonical, chemistry_class="spiegelmer_l_rna"),
        source_metadata=_meta(result.canonical),
        decision=result.decision,
    )
    assert detail["manual_decision"] == ""
    assert detail["manual_trim_action"] == ""
    assert detail["manual_molecule_type_override"] == ""


def test_target_and_s4_fields_remain_empty() -> None:
    result = _classify(_s2(sequence=_rna(40), native_id="t1"))
    assert result.canonical["target_name_raw"] == ""
    for field_name in S3_FORBIDDEN_FIELDS:
        assert result.canonical[field_name] == ""
    assert result.decision["target_name_raw"] == ""


def test_duplicate_freebase_ids_are_retained_independently() -> None:
    first = _classify(
        _s2(sequence=_rna(40), native_id="dup1"),
        aptamerbase_id="m.shared",
    )
    second = _classify(
        _s2(sequence=_rna(41), native_id="dup2"),
        aptamerbase_id="m.shared",
    )
    assert first.decision["aptamerbase_id"] == second.decision["aptamerbase_id"]
    assert first.canonical["record_id"] != second.canonical["record_id"]
    assert first.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert second.primary_route == PRIMARY_ROUTE_ELIGIBLE


def test_canonical_s3_remains_identical_to_s2() -> None:
    canonical = _s2(sequence=_rna(40), native_id="id1")
    result = _classify(canonical)
    for key, value in canonical.items():
        assert result.canonical[key] == value


def test_no_row_silently_disappears_from_closed_reasons() -> None:
    assert "non_aptamer_source_object" in PLAN_REJECTION_REASONS
    assert "non_aptamer_source_object" not in APTADB_PLAN_REJECTION
    assert "non_aptamer_source_object" not in RIBO_PLAN_REJECTION
    assert "non_aptamer_source_object" not in APTAINDEX_PLAN_REJECTION
    plan = REPO_ROOT / "docs" / "data_curation" / "rna_aptamer_corpus_curation_plan.md"
    plan_text = plan.read_text(encoding="utf-8")
    vocab_start = plan_text.index("**Rejection reason vocabulary (closed set):**")
    vocab_block = plan_text[vocab_start : vocab_start + 1200]
    assert "`non_aptamer_source_object`" in vocab_block
    assert "explicitly typed metadata/structure object" in vocab_block
