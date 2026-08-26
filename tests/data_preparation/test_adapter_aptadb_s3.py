"""Tests for the AptaDB S3 eligibility adapter (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. Does not read real
AptaDB source sequences.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb_s3 import (  # noqa: E402
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_NON_PROTEIN,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    apply_random_accept_audit,
    build_unlinked_rejection_row,
    classify_aptadb_record,
    unlinked_rejection_record_id,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import (  # noqa: E402
    EligibilityDecision,
    EligibilityReason,
    load_eligibility_policy,
)

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "aptadb.json"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _dna(n: int) -> str:
    return ("ACGT" * ((n // 4) + 1))[:n]


def _s2(
    *,
    sequence: str = "ACGUAC",
    molecule_type: str = "RNA",
    alphabet: str = "RNA",
    chemistry: str = "RNA",
    target: str = "demo_protein",
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
            "record_id": f"aptadb:{native_id}",
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
            "source_db": "aptadb",
            "source_dataset": "aptadb_official_export_2026-08",
            "contributing_sources": "aptadb",
            "contributing_datasets": "aptadb_official_export_2026-08",
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
        "aptamer_name": f"name-{canonical['native_id']}",
        "target_name_raw": canonical["target_name_raw"],
        "source_aptamer_chemistry": (
            "RNA" if canonical["molecule_type"] == "RNA" else "DNA"
        ),
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "alphabet_as_reported": canonical["alphabet_as_reported"],
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
    target_chemistry: str = "Protein",
    **overrides: str,
) -> dict[str, str]:
    row = {
        "record_id": canonical["record_id"],
        "aptadb_apta_index": f"Apta_{canonical['native_id']}",
        "aptadb_target_chemistry": target_chemistry,
        "aptadb_aptamer_chemistry": (
            "RNA" if canonical["molecule_type"] == "RNA" else "DNA"
        ),
        "aptadb_aptamer_description": f"name-{canonical['native_id']}",
        "aptadb_binding_conditions_buffer": "PBS",
        "aptadb_reference_pubmed_id": "11111111",
    }
    row.update(overrides)
    return row


def _classify(
    canonical: dict[str, str],
    *,
    target_chemistry: str = "Protein",
    proposals: list[dict[str, str]] | None = None,
    **meta: str,
):
    return classify_aptadb_record(
        canonical,
        _qc(canonical),
        _meta(canonical, target_chemistry=target_chemistry, **meta),
        policy=POLICY,
        proposals=proposals or (),
    )


def test_valid_rna_protein_is_technically_eligible() -> None:
    result = _classify(_s2(sequence=_rna(40), native_id="rna_prot"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert (
        result.eligibility.primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    )
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert result.park_row is None
    assert result.rejection_row is None


def test_valid_rna_molecule_parks_non_protein() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="rna_mol", target=""),
        target_chemistry="Molecule",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.NON_PROTEIN_TARGET_PARKED
    )
    assert result.primary_route == PRIMARY_ROUTE_NON_PROTEIN
    assert result.canonical["target_type"] == ""


def test_valid_rna_cell_parks_non_protein() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="rna_cell", target=""),
        target_chemistry="Cell",
    )
    assert result.primary_route == PRIMARY_ROUTE_NON_PROTEIN


def test_valid_rna_other_parks_non_protein() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="rna_other", target=""),
        target_chemistry="Other",
    )
    assert result.primary_route == PRIMARY_ROUTE_NON_PROTEIN


def test_valid_ssdna_protein_parks_ssdna() -> None:
    result = _classify(
        _s2(
            sequence=_dna(40),
            molecule_type="ssDNA",
            alphabet="DNA_T",
            chemistry="DNA",
            native_id="dna_prot",
        ),
        target_chemistry="Protein",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.SSDNA_PARKED
    assert result.primary_route == PRIMARY_ROUTE_SSDNA


def test_valid_ssdna_molecule_parks_ssdna_only() -> None:
    result = _classify(
        _s2(
            sequence=_dna(40),
            molecule_type="ssDNA",
            alphabet="DNA_T",
            chemistry="DNA",
            native_id="dna_mol",
            target="",
        ),
        target_chemistry="Molecule",
    )
    assert result.primary_route == PRIMARY_ROUTE_SSDNA
    assert (
        EligibilityReason.NON_PROTEIN_TARGET_PARKED
        not in result.eligibility.all_reasons
    )


def test_gapped_ssdna_rejects_before_park() -> None:
    seq = _dna(39) + "-"
    result = _classify(
        _s2(
            sequence=seq,
            molecule_type="ssDNA",
            alphabet="invalid",
            chemistry="DNA",
            qc_flags="alignment_gaps",
            native_id="dna_gap",
        ),
        target_chemistry="Protein",
    )
    assert result.primary_route == PRIMARY_ROUTE_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.ALIGNMENT_GAPS
    assert result.park_row is None
    assert result.rejection_row is not None


def test_gapped_rna_non_protein_rejects_before_park() -> None:
    seq = _rna(39) + "-"
    result = _classify(
        _s2(
            sequence=seq,
            qc_flags="alignment_gaps",
            native_id="rna_gap_np",
            target="",
        ),
        target_chemistry="Molecule",
    )
    assert result.primary_route == PRIMARY_ROUTE_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.ALIGNMENT_GAPS


def test_alignment_gaps_flag_rejects_without_invalid_character() -> None:
    seq = _rna(39) + "."
    result = _classify(
        _s2(
            sequence=seq,
            qc_flags="alignment_gaps",
            native_id="gap_flag",
        )
    )
    assert result.eligibility.primary_reason == EligibilityReason.ALIGNMENT_GAPS
    assert EligibilityReason.INVALID_ALPHABET not in result.eligibility.all_reasons
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"


def test_mixed_t_u_rejects() -> None:
    seq = _rna(20) + "T" + _rna(19)
    result = _classify(
        _s2(
            sequence=seq,
            alphabet="mixed_T_U",
            qc_flags="mixed_t_u",
            native_id="mixed",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.MIXED_T_AND_U
    assert result.eligibility.manual_review_required is True


def test_invalid_alphabet_rejects() -> None:
    result = _classify(
        _s2(
            sequence=_rna(39) + "X",
            alphabet="invalid",
            qc_flags="invalid_character",
            native_id="invalid",
        )
    )
    assert result.eligibility.primary_reason == EligibilityReason.INVALID_ALPHABET
    assert result.eligibility.manual_review_required is True


def test_length_19_rejects() -> None:
    result = _classify(_s2(sequence=_rna(19), native_id="short"))
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.manual_review_required is False
    assert result.decision["review_batch"] == ""


def test_length_20_is_valid_boundary() -> None:
    result = _classify(_s2(sequence=_rna(20), native_id="low"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.LOWER_LENGTH_BOUNDARY in result.eligibility.all_reasons
    assert result.decision["review_batch"] == "03_length_boundary"


def test_length_100_is_valid_boundary() -> None:
    result = _classify(_s2(sequence=_rna(100), native_id="high"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.UPPER_LENGTH_BOUNDARY in result.eligibility.all_reasons


def test_length_101_rejects() -> None:
    result = _classify(_s2(sequence=_rna(101), native_id="long"))
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.manual_review_required is False


def test_every_record_gets_exactly_one_primary_route() -> None:
    cases = [
        _classify(_s2(sequence=_rna(40), native_id="a")),
        _classify(
            _s2(sequence=_rna(40), native_id="b", target=""),
            target_chemistry="Cell",
        ),
        _classify(
            _s2(
                sequence=_dna(40),
                molecule_type="ssDNA",
                alphabet="DNA_T",
                chemistry="DNA",
                native_id="c",
            )
        ),
        _classify(_s2(sequence=_rna(19), native_id="d")),
    ]
    routes = [row.primary_route for row in cases]
    assert len(routes) == 4
    assert set(routes) <= {
        PRIMARY_ROUTE_REJECT,
        PRIMARY_ROUTE_SSDNA,
        PRIMARY_ROUTE_NON_PROTEIN,
        PRIMARY_ROUTE_ELIGIBLE,
    }
    ids = [row.canonical["record_id"] for row in cases]
    assert len(ids) == len(set(ids))


def test_unlinked_aptamer_missing_target_log_is_not_an_interaction() -> None:
    row = build_unlinked_rejection_row(
        {
            "apta_index": "Apta_99",
            "aptamer_chemistry": "DNA",
            "sequence": "ACGTAC",
            "planned_s3_reason": "missing_target",
        },
        source_dataset="aptadb_official_export_2026-08",
    )
    assert row["record_id"] == unlinked_rejection_record_id("Apta_99")
    assert row["record_id"].startswith("aptadb:unlinked:")
    assert row["native_id"] == "Apta_99"
    assert row["rejection_reason"] == "missing_target"
    assert row["stage"] == "S3_source_reconciliation"
    assert "aptadb:99" not in row["record_id"]


def test_random_accept_audit_is_deterministic() -> None:
    rows = []
    details = {}
    for i in range(1, 41):
        canonical = _s2(sequence=_rna(40), native_id=str(i))
        classified = _classify(canonical)
        rows.append(classified.decision)
        details[classified.decision["record_id"]] = {
            "secondary_reasons": classified.decision["secondary_reasons"],
            "manual_review_required": classified.decision["manual_review_required"],
            "manual_review_priority": classified.decision["manual_review_priority"],
            "review_batch": classified.decision["review_batch"],
            "checkpoint_review_reasons": classified.decision[
                "checkpoint_review_reasons"
            ],
        }
    first = [dict(row) for row in rows]
    take_a, pool_a, short_a = apply_random_accept_audit(
        rows, details, seed=42, sample_size=30
    )
    selected_a = {
        row["record_id"]
        for row in rows
        if "random_accept_audit" in row["secondary_reasons"]
    }
    assert take_a == 30
    assert pool_a == 40
    assert short_a == 0
    assert len(selected_a) == 30

    take_b, pool_b, _ = apply_random_accept_audit(
        first, {key: dict(val) for key, val in details.items()}, seed=42, sample_size=30
    )
    selected_b = {
        row["record_id"]
        for row in first
        if "random_accept_audit" in row["secondary_reasons"]
    }
    assert take_b == take_a
    assert pool_b == pool_a
    assert selected_a == selected_b


def test_constant_proposal_enters_review_but_is_not_trimmed() -> None:
    core = _rna(40)
    proposal = {
        "proposal_id": "grp:five_prime:group_consensus",
        "experiment_group_id": "grp",
        "proposal_source": "group_consensus",
        "side": "five_prime",
        "motif_length": "12",
        "support": "0.9",
        "records_considered": "8",
        "applied": "false",
    }
    result = _classify(
        _s2(sequence=core, native_id="prop", trim_confidence="n/a"),
        proposals=[proposal],
    )
    assert result.canonical["sequence_core"] == core
    assert result.canonical["sequence_full"] == core
    assert result.canonical["trim_confidence"] == "n/a"
    assert EligibilityReason.CONSTANT_REGION_PROPOSAL in result.eligibility.all_reasons
    assert result.eligibility.manual_review_required is True
    assert "constant_region_proposal" in result.decision["checkpoint_review_reasons"]
    assert result.decision["constant_proposal_ids"]


def test_review_reason_aggregation() -> None:
    proposal = {
        "proposal_id": "grp:five_prime:group_consensus",
        "experiment_group_id": "grp",
        "proposal_source": "group_consensus",
        "side": "five_prime",
        "motif_length": "12",
        "support": "0.85",
        "records_considered": "6",
        "applied": "false",
    }
    result = _classify(
        _s2(sequence=_rna(22), native_id="combo"),
        proposals=[proposal],
    )
    reasons = set(result.decision["checkpoint_review_reasons"].split("|"))
    assert "length_boundary" in reasons
    assert "constant_region_proposal" in reasons
    assert result.decision["review_batch"] == "02_constant_region_proposal"


def test_s4_fields_remain_untouched() -> None:
    result = _classify(_s2(sequence=_rna(40), native_id="s4"))
    for field in S3_FORBIDDEN_FIELDS:
        assert result.canonical[field] == ""
    assert "target_type" not in result.decision
    assert "binding_evidence_score" not in result.decision
    assert result.canonical["target_name"] == ""
    assert result.canonical["binding_evidence_score"] == ""
    assert result.canonical["pdb_id"] == ""
