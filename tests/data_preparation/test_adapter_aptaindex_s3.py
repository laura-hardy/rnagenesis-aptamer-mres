"""Tests for the AptaIndex S3 eligibility adapter (synthetic only).

Every literal nucleotide string is a runtime-built ACGU/ACGT tile.
Does not read or embed real AptaIndex sequences.
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
    PLAN_REJECTION_REASONS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    AptaIndexS3Error,
    apply_random_accept_audit,
    classify_aptaindex_record,
    count_multi_target_sequences,
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
    REPO_ROOT / "config" / "source_eligibility" / "aptaindex.json"
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
    alphabet: str = "chemical_notation",
    target: str = "demo_target",
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
            "record_id": f"aptaindex:{native_id}",
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
            "target_name_raw": target,
            "source_db": "aptaindex",
            "source_dataset": "aptaindex_export_2026-07-22",
            "contributing_sources": "aptaindex",
            "contributing_datasets": "aptaindex_export_2026-07-22",
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
    mapping_class: str = "straightforward_rna",
    parser_status: str = "ok",
    parser_reason_category: str = "",
    source_type: str = "RNA",
    token_family_summary: str = "r",
    has_l_prefix: str = "false",
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "source_type": source_type,
        "parser_status": parser_status,
        "parser_reason_category": parser_reason_category,
        "mapping_class": mapping_class,
        "token_family_summary": token_family_summary,
        "has_l_prefix": has_l_prefix,
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
    aptaindex_type: str = "RNA",
    aptaindex_target_type: str = "Protein",
    aptaindex_target: str | None = None,
    **overrides: str,
) -> dict[str, str]:
    target = (
        canonical["target_name_raw"] if aptaindex_target is None else aptaindex_target
    )
    row = {
        "record_id": canonical["record_id"],
        "aptaindex_native_id": canonical["native_id"],
        "aptaindex_title": f"title-{canonical['native_id']}",
        "aptaindex_type": aptaindex_type,
        "aptaindex_target": target,
        "aptaindex_target_type": aptaindex_target_type,
        "aptaindex_affinity_type": "",
        "aptaindex_affinity": "",
        "aptaindex_affinity_units": "",
        "aptaindex_binding_conditions": "",
        "aptaindex_reference": "Demo",
    }
    row.update(overrides)
    return row


def _classify(
    canonical: dict[str, str],
    *,
    mapping_class: str = "straightforward_rna",
    parser_status: str = "ok",
    parser_reason_category: str = "",
    source_type: str = "RNA",
    token_family_summary: str = "r",
    has_l_prefix: str = "false",
    aptaindex_type: str = "RNA",
    aptaindex_target_type: str = "Protein",
    proposals: list[dict[str, str]] | None = None,
    **meta: str,
):
    return classify_aptaindex_record(
        canonical,
        _qc(
            canonical,
            mapping_class=mapping_class,
            parser_status=parser_status,
            parser_reason_category=parser_reason_category,
            source_type=source_type,
            token_family_summary=token_family_summary,
            has_l_prefix=has_l_prefix,
        ),
        _meta(
            canonical,
            aptaindex_type=aptaindex_type,
            aptaindex_target_type=aptaindex_target_type,
            **meta,
        ),
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
    assert POLICY.random_accept_audit_size == 30
    assert POLICY.random_seed == 42


def test_missing_sequence_is_automatic_reject_not_review() -> None:
    result = _classify(
        _s2(sequence="", native_id="0002", qc_flags="missing_sequence"),
        mapping_class="missing_sequence",
        parser_status="missing",
        source_type="DNA",
        aptaindex_type="DNA",
        token_family_summary="",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    assert result.eligibility.manual_review_required is False
    assert result.decision["review_batch"] == ""
    assert result.rejection_row is not None
    assert result.rejection_row["rejection_reason"] == "missing_sequence"


def test_straightforward_ssdna_is_parked_not_rejected() -> None:
    result = _classify(
        _s2(
            sequence=_dna(40),
            native_id="0003",
            molecule_type="ssDNA",
            chemistry="DNA",
        ),
        mapping_class="straightforward_dna",
        source_type="DNA",
        aptaindex_type="DNA",
        token_family_summary="d",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.SSDNA_PARKED
    assert result.primary_route == PRIMARY_ROUTE_SSDNA
    assert result.rejection_row is None
    assert result.park_row is not None
    assert "T" in result.canonical["sequence_core"]
    assert result.canonical["t_to_u_applied"] == "false"


def test_straightforward_rna_remains_eligible() -> None:
    result = _classify(_s2(sequence=_rna(40), native_id="0004"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert (
        result.eligibility.primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    )
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert result.rejection_row is None
    for field_name in S3_FORBIDDEN_FIELDS:
        assert result.canonical.get(field_name, "") == ""


def test_straightforward_2f_rna_remains_eligible() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="0005",
            chemistry="2F-RNA",
        ),
        mapping_class="straightforward_2f_rna",
        source_type="2'-F-RNA",
        aptaindex_type="2'-F-RNA",
        token_family_summary="f+r",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert result.canonical["chemistry"] == "2F-RNA"


def test_peptide_molecule_is_non_nucleic_acid_reject() -> None:
    canonical = _s2(
        sequence="",
        native_id="0006",
        qc_flags="parser_not_applicable_peptide",
        alphabet="",
    )
    canonical["alphabet_as_reported"] = ""
    result = _classify(
        canonical,
        mapping_class="peptide",
        parser_status="not_applicable_peptide",
        source_type="Peptide",
        aptaindex_type="Peptide",
        token_family_summary="",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.NON_NUCLEIC_ACID_MOLECULE
    )
    assert result.eligibility.manual_review_required is False
    assert result.rejection_row is not None
    assert result.rejection_row["rejection_reason"] == "non_nucleic_acid_molecule"
    assert result.eligibility.primary_reason != EligibilityReason.NON_PROTEIN_TARGET_PARKED
    assert result.eligibility.primary_reason != EligibilityReason.INVALID_ALPHABET
    assert result.eligibility.primary_reason != EligibilityReason.SSDNA_PARKED


def test_peptide_target_alone_does_not_trigger_peptide_molecule() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="0007"),
        aptaindex_target_type="Peptide",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.NON_NUCLEIC_ACID_MOLECULE not in (
        result.eligibility.all_reasons
    )
    assert result.decision["aptaindex_target_type"] == "Peptide"


def test_unsupported_notation_is_review_not_invalid_alphabet() -> None:
    canonical = _s2(
        sequence="",
        native_id="0008",
        qc_flags="unsupported_notation",
        alphabet="chemical_notation",
    )
    canonical["alphabet_as_reported"] = "chemical_notation"
    canonical["molecule_type"] = "unknown"
    canonical["chemistry"] = "unknown"
    result = _classify(
        canonical,
        mapping_class="unsupported_notation",
        parser_status="failed",
        parser_reason_category="unsupported_decoration",
        source_type="RNA",
        aptaindex_type="RNA",
        token_family_summary="",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.UNSUPPORTED_CHEMICAL_NOTATION
    )
    assert result.primary_route == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"
    assert "unsupported_chemical_notation" in result.decision["checkpoint_review_reasons"]
    assert result.eligibility.primary_reason != EligibilityReason.INVALID_ALPHABET
    assert result.canonical["sequence_core"] == ""
    assert result.decision["parser_reason_category"] == "unsupported_decoration"


def test_l_rna_becomes_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="0009",
            molecule_type="unknown",
            chemistry="unknown",
        ),
        mapping_class="l_rna",
        source_type="L-RNA",
        aptaindex_type="L-RNA",
        token_family_summary="r",
        has_l_prefix="true",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.L_RNA_STEREOCHEMISTRY
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"
    assert result.primary_route != PRIMARY_ROUTE_ELIGIBLE


def test_l_dna_becomes_review() -> None:
    result = _classify(
        _s2(
            sequence=_dna(40),
            native_id="0010",
            molecule_type="unknown",
            chemistry="unknown",
        ),
        mapping_class="l_dna",
        source_type="L-DNA",
        aptaindex_type="L-DNA",
        token_family_summary="d",
        has_l_prefix="true",
    )
    assert result.eligibility.primary_reason == EligibilityReason.L_DNA_STEREOCHEMISTRY
    assert result.primary_route == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert result.primary_route != PRIMARY_ROUTE_SSDNA


def test_chimeric_becomes_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            native_id="0011",
            molecule_type="unknown",
            chemistry="unknown",
        ),
        mapping_class="chimeric",
        source_type="Chimeric",
        aptaindex_type="Chimeric",
        token_family_summary="d+r",
    )
    assert result.eligibility.primary_reason == EligibilityReason.CHIMERIC_MOLECULE
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"


def test_type_token_disagreement_becomes_review() -> None:
    result = _classify(
        _s2(
            sequence=_dna(40),
            native_id="0012",
            molecule_type="ssDNA",
            chemistry="DNA",
        ),
        mapping_class="type_token_disagreement",
        source_type="RNA",
        aptaindex_type="RNA",
        token_family_summary="d",
    )
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.SOURCE_TYPE_TOKEN_DISAGREEMENT
    )
    assert result.primary_route == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"


def test_mixed_t_u_is_classified_and_enters_judgement_review() -> None:
    mixed = ("ACGU" * 9) + "T" + ("ACGU" * 1)
    mixed = mixed[:40]
    result = _classify(
        _s2(sequence=mixed, native_id="0013", qc_flags="mixed_t_u"),
        mapping_class="straightforward_rna",
    )
    assert EligibilityReason.MIXED_T_AND_U in result.eligibility.all_reasons
    assert result.eligibility.primary_reason == EligibilityReason.MIXED_T_AND_U
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"
    assert result.canonical["sequence_core"] == mixed


def test_mixed_t_u_on_disagreement_parks_chemistry_with_mixed_secondary() -> None:
    mixed = ("ACGT" * 9) + "U" + ("ACGT" * 1)
    mixed = mixed[:40]
    result = _classify(
        _s2(
            sequence=mixed,
            native_id="0014",
            molecule_type="ssDNA",
            chemistry="DNA",
            qc_flags="mixed_t_u|source_type_token_disagreement",
        ),
        mapping_class="type_token_disagreement",
        source_type="RNA",
        aptaindex_type="RNA",
        token_family_summary="d+r",
    )
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.SOURCE_TYPE_TOKEN_DISAGREEMENT
    )
    assert EligibilityReason.MIXED_T_AND_U in result.eligibility.all_reasons
    assert result.primary_route == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert result.eligibility.manual_review_required is True


def test_length_below_20_rejects_parsed_rna() -> None:
    result = _classify(_s2(sequence=_rna(19), native_id="0015"))
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.manual_review_required is False


def test_length_above_100_rejects_parsed_rna() -> None:
    result = _classify(_s2(sequence=_rna(101), native_id="0016"))
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT


def test_length_does_not_apply_to_missing_peptide_or_unsupported() -> None:
    missing = _classify(
        _s2(sequence="", native_id="0017", qc_flags="missing_sequence"),
        mapping_class="missing_sequence",
        parser_status="missing",
        source_type="RNA",
        aptaindex_type="RNA",
    )
    peptide_row = _s2(
        sequence="",
        native_id="0018",
        qc_flags="parser_not_applicable_peptide",
        alphabet="",
    )
    peptide_row["alphabet_as_reported"] = ""
    peptide = _classify(
        peptide_row,
        mapping_class="peptide",
        parser_status="not_applicable_peptide",
        source_type="Peptide",
        aptaindex_type="Peptide",
    )
    unsupported_row = _s2(
        sequence="",
        native_id="0019",
        qc_flags="unsupported_notation",
        alphabet="chemical_notation",
    )
    unsupported_row["alphabet_as_reported"] = "chemical_notation"
    unsupported_row["molecule_type"] = "unknown"
    unsupported = _classify(
        unsupported_row,
        mapping_class="unsupported_notation",
        parser_status="failed",
        parser_reason_category="unsupported_decoration",
        source_type="RNA",
        aptaindex_type="RNA",
    )
    for result in (missing, peptide, unsupported):
        assert EligibilityReason.LENGTH_OUT_OF_RANGE not in result.eligibility.all_reasons


def test_20_25_otherwise_kept_enters_boundary_audit() -> None:
    result = _classify(_s2(sequence=_rna(22), native_id="0020"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.decision["review_batch"] == "03_length_boundary"
    assert "length_boundary" in result.decision["checkpoint_review_reasons"]


def test_90_100_otherwise_kept_enters_boundary_audit() -> None:
    result = _classify(_s2(sequence=_rna(95), native_id="0021"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.decision["review_batch"] == "03_length_boundary"


def test_known_motif_proposal_enters_trim_review() -> None:
    canonical = _s2(sequence=_rna(40), native_id="0022")
    result = _classify(
        canonical,
        proposals=[_known_motif(canonical["record_id"])],
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.KNOWN_MOTIF_PROPOSAL in result.eligibility.all_reasons
    assert result.decision["review_batch"] == "02_constant_region_proposal"
    assert result.canonical["sequence_core"] == canonical["sequence_core"]


def test_multi_target_copies_are_not_s3_conflicts() -> None:
    seq = _rna(40)
    rows = [
        _s2(sequence=seq, native_id="0023", target="target_a"),
        _s2(sequence=seq, native_id="0024", target="target_b"),
    ]
    assert count_multi_target_sequences(rows) == 1
    first = _classify(rows[0])
    second = _classify(rows[1])
    assert first.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert second.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert first.decision["notes"] == ""
    assert "conflict" not in first.decision["primary_reason"]


def test_missing_target_is_deferred_not_rejected() -> None:
    result = _classify(_s2(sequence=_rna(40), native_id="0025", target=""))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.MISSING_TARGET not in result.eligibility.all_reasons
    assert result.canonical["target_name_raw"] == ""
    assert result.canonical["target_name"] == ""


def test_target_evidence_affinity_remain_empty() -> None:
    result = _classify(_s2(sequence=_rna(40), native_id="0026"))
    for field_name in (
        "target_name",
        "target_type",
        "binding_evidence_score",
        "affinity_value",
        "affinity_unit",
        "affinity_type",
    ):
        assert result.canonical[field_name] == ""


def test_random_kept_sample_is_deterministic() -> None:
    decisions = []
    details = {}
    for index in range(1, 8):
        native = f"{index:04d}"
        canonical = _s2(sequence=_rna(40), native_id=native)
        classified = _classify(canonical)
        decisions.append(classified.decision)
        details[classified.decision["record_id"]] = {
            "record_id": classified.decision["record_id"],
            "secondary_reasons": classified.decision["secondary_reasons"],
            "checkpoint_review_reasons": classified.decision[
                "checkpoint_review_reasons"
            ],
            "manual_review_required": classified.decision["manual_review_required"],
            "manual_review_priority": classified.decision["manual_review_priority"],
            "review_batch": classified.decision["review_batch"],
        }
    first = [dict(row) for row in decisions]
    second = [dict(row) for row in decisions]
    apply_random_accept_audit(first, details, seed=42, sample_size=3)
    apply_random_accept_audit(second, {key: dict(value) for key, value in details.items()}, seed=42, sample_size=3)
    sampled_first = {
        row["record_id"]
        for row in first
        if "random_accept_audit" in row["secondary_reasons"]
    }
    sampled_second = {
        row["record_id"]
        for row in second
        if "random_accept_audit" in row["secondary_reasons"]
    }
    assert sampled_first == sampled_second
    assert len(sampled_first) == 3
    for row in first:
        if row["record_id"] in sampled_first:
            assert row["review_batch"] == "04_random_kept_audit"


def test_no_row_silently_disappears_from_closed_reasons() -> None:
    assert "non_nucleic_acid_molecule" in PLAN_REJECTION_REASONS
    assert "non_nucleic_acid_molecule" not in APTADB_PLAN_REJECTION
    assert "non_nucleic_acid_molecule" not in RIBO_PLAN_REJECTION
    plan = (REPO_ROOT / "docs" / "data_curation" / "rna_aptamer_corpus_curation_plan.md")
    plan_text = plan.read_text(encoding="utf-8")
    vocab_start = plan_text.index("**Rejection reason vocabulary (closed set):**")
    vocab_block = plan_text[vocab_start : vocab_start + 900]
    assert "`non_nucleic_acid_molecule`" in vocab_block
    assert "source-declared non-nucleic-acid aptamer/molecule record" in vocab_block


def test_group_consensus_proposals_are_forbidden() -> None:
    with pytest.raises(AptaIndexS3Error, match="group_consensus"):
        index_constant_proposals(
            [_s2(sequence=_rna(40), native_id="0027")],
            [
                {
                    "proposal_id": "x",
                    "experiment_group_id": "aptaindex:0027",
                    "proposal_source": "group_consensus",
                }
            ],
        )


def test_l_rna_missing_sequence_stays_missing_sequence() -> None:
    result = _classify(
        _s2(sequence="", native_id="0028", qc_flags="missing_sequence"),
        mapping_class="missing_sequence",
        parser_status="missing",
        source_type="L-RNA",
        aptaindex_type="L-RNA",
    )
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    assert result.eligibility.manual_review_required is False
