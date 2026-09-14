"""Tests for the NCBI Nucleotide S3 eligibility adapter (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt, except
programmatically generated repeats used to exercise length QC. Does not
read real NCBI aptamer sequences.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.ncbi_nuc import SIDECAR_COLUMNS  # noqa: E402
from adapters.ncbi_nuc_s2 import S2_QC_COLUMNS  # noqa: E402
from adapters.ncbi_nuc_s3 import (  # noqa: E402
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
    NcbiNucS3Error,
    apply_random_accept_audit,
    classify_ncbi_nuc_record,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import (  # noqa: E402
    EligibilityDecision,
    EligibilityReason,
    load_eligibility_policy,
)

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "ncbi_nuc.json"
)

SYNTHETIC_RNA_36 = "ACGU" * 9
SYNTHETIC_RNA_99 = "ACGU" * 24 + "ACG"
SYNTHETIC_RNA_22 = "ACGU" * 5 + "AC"
SYNTHETIC_DNA_36 = "ACGT" * 9
SYNTHETIC_DNA_170 = "ACGT" * 42 + "AC"
SYNTHETIC_SHORT = "ACGT" * 3
SYNTHETIC_N_12 = "ACGT" * 2 + "ACGN"
SYNTHETIC_POLY_A = "A" * 11


def _s2(
    *,
    native_id: str,
    sequence: str,
    molecule_type: str,
    chemistry: str,
    alphabet: str,
    qc_flags: str = "",
    construct_scope: str = "unknown",
    t_to_u_applied: str = "false",
    **overrides: str,
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"ncbi_nuc:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": construct_scope,
            "trim_status": "no_constants_detected" if sequence else "not_applicable",
            "trim_confidence": "n/a",
            "molecule_type": molecule_type,
            "alphabet_as_reported": alphabet,
            "t_to_u_applied": t_to_u_applied,
            "chemistry": chemistry,
            "target_name_raw": "",
            "source_db": "ncbi_nuc",
            "source_dataset": "ncbi_nuc_genbank_2026-07-27",
            "contributing_sources": "ncbi_nuc",
            "contributing_datasets": "ncbi_nuc_genbank_2026-07-27",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "qc_flags": qc_flags,
        }
    )
    record.update(overrides)
    return record


def _qc(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {column: "" for column in S2_QC_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "target_name_raw": canonical["target_name_raw"],
            "alphabet_as_reported": canonical["alphabet_as_reported"],
            "molecule_type": canonical["molecule_type"],
            "chemistry": canonical["chemistry"],
            "t_to_u_applied": canonical["t_to_u_applied"],
            "sequence_length_full": canonical["sequence_length_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "construct_scope": canonical["construct_scope"],
            "trim_status": canonical["trim_status"],
            "trim_confidence": canonical["trim_confidence"],
            "qc_flags": canonical["qc_flags"],
            "primer_associated": "false",
            "cdna_template_associated": "false",
            "transcription_template": "false",
            "poly_a_fragment": "false",
            "possible_non_aptamer_source_object": "false",
            "construct_requires_review": "false",
            "group_consensus_proposal": "false",
            "known_motif_detected": "false",
        }
    )
    row.update(overrides)
    return row


def _meta(canonical: dict[str, str]) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "ncbi_nuc_accession": canonical["native_id"],
        }
    )
    return row


def _classify(canonical: dict[str, str], qc: dict[str, str] | None = None, **kwargs):
    return classify_ncbi_nuc_record(
        canonical,
        qc if qc is not None else _qc(canonical),
        _meta(canonical),
        policy=POLICY,
        **kwargs,
    )


def _secondaries(result) -> set[str]:
    return {reason.value for reason in result.eligibility.secondary_reasons}


def test_clear_rna_is_proposed_technical_accept() -> None:
    result = _classify(
        _s2(
            native_id="RNA36",
            sequence=SYNTHETIC_RNA_36,
            molecule_type="RNA",
            chemistry="RNA",
            alphabet="RNA",
            t_to_u_applied="true",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.eligibility.primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert result.rejection_row is None
    assert result.park_row is None
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["target_name_raw"] == ""
    for field in S3_FORBIDDEN_FIELDS:
        assert result.canonical.get(field, "") == ""


def test_unknown_construct_does_not_block_clear_rna() -> None:
    result = _classify(
        _s2(
            native_id="RNA36U",
            sequence=SYNTHETIC_RNA_36,
            molecule_type="RNA",
            chemistry="RNA",
            alphabet="RNA",
            construct_scope="unknown",
            t_to_u_applied="true",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED not in result.eligibility.all_reasons


def test_upper_boundary_rna_is_accepted_and_audited() -> None:
    result = _classify(
        _s2(
            native_id="RNA99",
            sequence=SYNTHETIC_RNA_99,
            molecule_type="RNA",
            chemistry="RNA",
            alphabet="RNA",
            t_to_u_applied="true",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "04_length_boundary"
    assert "length_boundary" in result.decision["checkpoint_review_reasons"]
    assert EligibilityReason.UPPER_LENGTH_BOUNDARY in result.eligibility.secondary_reasons


def test_valid_length_unknown_molecule_is_parked_for_review() -> None:
    result = _classify(
        _s2(
            native_id="UNK36",
            sequence=SYNTHETIC_DNA_36,
            molecule_type="unknown",
            chemistry="unknown",
            alphabet="DNA_T",
            qc_flags="molecule_type_unknown",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    assert result.primary_route == PRIMARY_ROUTE_MOLECULE
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "02_molecule_type_unresolved"
    assert result.park_row is not None
    assert result.rejection_row is None


def test_short_unknown_molecule_keeps_length_as_secondary() -> None:
    result = _classify(
        _s2(
            native_id="UNK12",
            sequence=SYNTHETIC_SHORT,
            molecule_type="unknown",
            chemistry="unknown",
            alphabet="DNA_T",
            qc_flags="molecule_type_unknown",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    assert EligibilityReason.LENGTH_OUT_OF_RANGE.value in _secondaries(result)


def test_ambiguous_unknown_molecule_keeps_n_as_secondary() -> None:
    result = _classify(
        _s2(
            native_id="UNKN",
            sequence=SYNTHETIC_N_12,
            molecule_type="unknown",
            chemistry="unknown",
            alphabet="ambiguous",
            qc_flags="molecule_type_unknown|ambiguous_base",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    assert EligibilityReason.AMBIGUOUS_BASES.value in _secondaries(result)
    assert result.canonical["sequence_core"] == SYNTHETIC_N_12


def test_alphabet_rna_does_not_resolve_unknown_molecule() -> None:
    result = _classify(
        _s2(
            native_id="POLYA",
            sequence=SYNTHETIC_POLY_A,
            molecule_type="unknown",
            chemistry="unknown",
            alphabet="RNA",
            qc_flags="molecule_type_unknown|poly_a_fragment",
        ),
        _qc(
            _s2(
                native_id="POLYA",
                sequence=SYNTHETIC_POLY_A,
                molecule_type="unknown",
                chemistry="unknown",
                alphabet="RNA",
                qc_flags="molecule_type_unknown|poly_a_fragment",
            ),
            poly_a_fragment="true",
            source_object_class="poly_a_fragment",
            construct_requires_review="true",
        ),
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert result.eligibility.proposed_decision != EligibilityDecision.PROPOSED_ACCEPT
    assert result.eligibility.primary_reason == EligibilityReason.NON_APTAMER_SOURCE_OBJECT


def test_explicit_primer_is_primer_like_reject_with_review() -> None:
    canonical = _s2(
        native_id="PRIMER",
        sequence=SYNTHETIC_DNA_36,
        molecule_type="unknown",
        chemistry="unknown",
        alphabet="DNA_T",
        qc_flags="molecule_type_unknown|primer_associated",
        construct_scope="partial_construct",
    )
    result = _classify(
        canonical,
        _qc(
            canonical,
            primer_associated="true",
            source_object_class="primer_associated",
            construct_requires_review="true",
        ),
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.PRIMER_LIKE
    assert result.primary_route == PRIMARY_ROUTE_REJECT
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"
    assert result.rejection_row is not None
    assert result.rejection_row["rejection_reason"] == "primer_like"
    assert EligibilityReason.MOLECULE_TYPE_UNRESOLVED.value in _secondaries(result)


def test_short_primer_does_not_let_length_bypass_primer_review() -> None:
    canonical = _s2(
        native_id="PRIMER19",
        sequence="ACGT" * 4 + "ACG",
        molecule_type="unknown",
        chemistry="unknown",
        alphabet="DNA_T",
        qc_flags="molecule_type_unknown|primer_associated",
        construct_scope="partial_construct",
    )
    result = _classify(
        canonical,
        _qc(
            canonical,
            primer_associated="true",
            source_object_class="primer_associated",
            construct_requires_review="true",
        ),
    )
    assert result.eligibility.primary_reason == EligibilityReason.PRIMER_LIKE
    assert EligibilityReason.LENGTH_OUT_OF_RANGE.value in _secondaries(result)


def test_poly_a_fragment_is_non_aptamer_source_object_reject() -> None:
    canonical = _s2(
        native_id="POLYA2",
        sequence=SYNTHETIC_POLY_A,
        molecule_type="unknown",
        chemistry="unknown",
        alphabet="RNA",
        qc_flags="molecule_type_unknown|poly_a_fragment",
        construct_scope="partial_construct",
    )
    result = _classify(
        canonical,
        _qc(
            canonical,
            poly_a_fragment="true",
            source_object_class="poly_a_fragment",
            construct_requires_review="true",
        ),
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.NON_APTAMER_SOURCE_OBJECT
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"
    assert result.canonical["molecule_type"] != "RNA"


def test_method_dna_object_is_source_object_reject_not_dna_park() -> None:
    canonical = _s2(
        native_id="METHODDNA",
        sequence=SYNTHETIC_DNA_170,
        molecule_type="DNA",
        chemistry="DNA",
        alphabet="DNA_T",
        qc_flags="possible_non_aptamer_source_object",
    )
    result = _classify(
        canonical,
        _qc(
            canonical,
            possible_non_aptamer_source_object="true",
            source_object_class="possible_non_aptamer_method_object",
        ),
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.NON_APTAMER_SOURCE_OBJECT
    assert result.primary_route == PRIMARY_ROUTE_REJECT
    assert result.park_row is None
    assert result.rejection_row is not None
    assert result.canonical["molecule_type"] == "DNA"
    assert result.canonical["chemistry"] == "DNA"
    assert EligibilityReason.LENGTH_OUT_OF_RANGE.value in _secondaries(result)


def test_transcription_template_is_unresolved_park_with_construct_review() -> None:
    canonical = _s2(
        native_id="TEMPLATE",
        sequence=SYNTHETIC_DNA_36,
        molecule_type="unknown",
        chemistry="unknown",
        alphabet="DNA_T",
        qc_flags="molecule_type_unknown|transcription_template",
        construct_scope="full_construct",
    )
    result = _classify(
        canonical,
        _qc(
            canonical,
            transcription_template="true",
            source_object_class="transcription_template",
            construct_requires_review="true",
        ),
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    assert "construct_source_object" in result.decision["checkpoint_review_reasons"]
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]


def test_cdna_with_no_safe_core_is_unresolved_park() -> None:
    canonical = _s2(
        native_id="CDNA",
        sequence=SYNTHETIC_DNA_36,
        molecule_type="unknown",
        chemistry="unknown",
        alphabet="DNA_T",
        qc_flags="molecule_type_unknown|cdna_template_associated",
    )
    result = _classify(
        canonical,
        _qc(
            canonical,
            cdna_template_associated="true",
            source_object_class="cdna_template_associated",
            construct_requires_review="true",
        ),
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    assert result.eligibility.manual_review_required is True


def test_no_trim_applied_and_core_equals_full() -> None:
    result = _classify(
        _s2(
            native_id="RNA36B",
            sequence=SYNTHETIC_RNA_36,
            molecule_type="RNA",
            chemistry="RNA",
            alphabet="RNA",
            t_to_u_applied="true",
        )
    )
    assert result.canonical["sequence_core"] == SYNTHETIC_RNA_36
    assert result.canonical["sequence_full"] == SYNTHETIC_RNA_36
    assert result.canonical["trim_status"] == "no_constants_detected"


def test_group_consensus_proposal_hard_fails() -> None:
    canonical = _s2(
        native_id="RNA36C",
        sequence=SYNTHETIC_RNA_36,
        molecule_type="RNA",
        chemistry="RNA",
        alphabet="RNA",
        t_to_u_applied="true",
    )
    with pytest.raises(NcbiNucS3Error, match="Group-consensus"):
        _classify(
            canonical,
            proposals=[
                {
                    "proposal_id": "x",
                    "proposal_source": "group_consensus",
                    "applied": "false",
                }
            ],
        )


def test_unexpected_known_motif_is_not_applied() -> None:
    canonical = _s2(
        native_id="RNA36M",
        sequence=SYNTHETIC_RNA_36,
        molecule_type="RNA",
        chemistry="RNA",
        alphabet="RNA",
        t_to_u_applied="true",
    )
    result = _classify(
        canonical,
        proposals=[
            {
                "proposal_id": "ncbi_nuc:RNA36M:known_motif:five_prime:t7",
                "proposal_source": "known_motif",
                "applied": "false",
                "side": "five_prime",
            }
        ],
    )
    assert result.canonical["sequence_core"] == SYNTHETIC_RNA_36
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.KNOWN_MOTIF_PROPOSAL in result.eligibility.secondary_reasons
    assert "constant_region_proposal" in result.decision["checkpoint_review_reasons"]
    assert result.eligibility.manual_review_required is True


def test_random_audit_does_not_fabricate_rows() -> None:
    canonical = _s2(
        native_id="RNA36D",
        sequence=SYNTHETIC_RNA_36,
        molecule_type="RNA",
        chemistry="RNA",
        alphabet="RNA",
        t_to_u_applied="true",
    )
    result = _classify(canonical)
    decisions = [dict(result.decision)]
    local = {result.canonical["record_id"]: dict(result.decision)}
    take, pool, shortfall = apply_random_accept_audit(
        decisions,
        local,
        seed=42,
        sample_size=30,
    )
    assert pool == 1
    assert take == 1
    assert shortfall == 29
    assert decisions[0]["manual_review_required"] == "true"
    assert "random_kept_audit" in decisions[0]["checkpoint_review_reasons"]


def test_s3_must_not_receive_applied_trim() -> None:
    canonical = _s2(
        native_id="TRIMMED",
        sequence=SYNTHETIC_RNA_36,
        molecule_type="RNA",
        chemistry="RNA",
        alphabet="RNA",
        t_to_u_applied="true",
        sequence_core=SYNTHETIC_RNA_36[5:],
        sequence_length_core=str(len(SYNTHETIC_RNA_36) - 5),
    )
    with pytest.raises(NcbiNucS3Error, match="applied trim"):
        _classify(canonical)
