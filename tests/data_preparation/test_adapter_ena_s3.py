"""Tests for the ENA S3 eligibility adapter (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. Does not read real
ENA source sequences.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.ena import SIDECAR_COLUMNS  # noqa: E402
from adapters.ena_s3 import (  # noqa: E402
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    apply_duplicate_sequence_diagnostic,
    apply_random_accept_audit,
    classify_ena_record,
    duplicate_sequence_full_ids,
    index_constant_proposals,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import (  # noqa: E402
    EligibilityDecision,
    EligibilityReason,
    load_eligibility_policy,
)

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "ena.json"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _s2(
    *,
    sequence: str = "ACGUACGUACGUACGUACGU",
    alphabet: str = "RNA",
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
    trim_confidence: str = "n/a",
    native_id: str = "ru001",
    t_to_u_applied: str = "false",
    target: str = "demo_target",
    **overrides: str,
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"ena:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "trim_confidence": trim_confidence,
            "molecule_type": "RNA",
            "alphabet_as_reported": alphabet if sequence else "missing",
            "t_to_u_applied": t_to_u_applied,
            "chemistry": "RNA",
            "target_name_raw": target,
            "source_db": "ena",
            "source_dataset": "ena_selected_v2_2026-08",
            "contributing_sources": "ena",
            "contributing_datasets": "ena_selected_v2_2026-08",
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
    row = {
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
        "experiment_group_id": "g1",
        "source_promoter_or_template_concern": "false",
        "source_t7_concern": "false",
        "sequence_corrected_applied": "0",
        "group_consensus_proposal": "false",
    }
    row.update(overrides)
    return row


def _meta(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "review_unit_id": canonical["native_id"],
            "sequence": canonical["sequence_raw"],
            "target": canonical["target_name_raw"],
            "target_type": "protein",
            "experiment_group_id": "g1",
            "binding_evidence_type": "SELEX",
            "binding_evidence_strength": "weak",
            "unresolved_target": "0",
            "genuine_target_conflict": "0",
        }
    )
    row.update(overrides)
    return row


def _proposal(
    *,
    group_id: str = "g1",
    side: str = "five_prime",
    motif: str = "ACGU",
    support: str = "0.80",
) -> dict[str, str]:
    return {
        "proposal_id": f"{group_id}:{side}:group_consensus",
        "experiment_group_id": group_id,
        "proposal_source": "group_consensus",
        "side": side,
        "proposed_sequence": motif,
        "motif_id": "",
        "motif_length": str(len(motif)),
        "support": support,
        "records_considered": "8",
        "records_matching_exactly": "8",
        "confidence": "medium",
        "status": "candidate",
        "applied": "false",
        "reason_not_applied": "unapplied_pending_checkpoint",
        "reason": "",
    }


def _classify(
    canonical: dict[str, str],
    *,
    proposals: list[dict[str, str]] | None = None,
    qc: dict[str, str] | None = None,
    meta: dict[str, str] | None = None,
):
    return classify_ena_record(
        canonical,
        qc or _qc(canonical),
        meta or _meta(canonical),
        policy=POLICY,
        proposals=proposals or (),
    )


def test_valid_ena_rna_proposed_accept() -> None:
    result = _classify(_s2(sequence=_rna(40)))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.eligibility.primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert result.rejection_row is None
    assert result.park_row is None


def test_t_transcribed_valid_rna_is_accept_not_dna_park() -> None:
    seq = _rna(40)
    result = _classify(
        _s2(
            sequence=seq,
            alphabet="DNA_T",
            t_to_u_applied="true",
            qc_flags="t_in_reported_rna",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert result.eligibility.primary_reason != EligibilityReason.SSDNA_PARKED
    assert result.eligibility.primary_reason != EligibilityReason.NON_RNA_MOLECULE
    assert "t_to_u_transcription_audit" in result.decision["checkpoint_review_reasons"]
    assert result.decision["review_batch"] == "02_transcription_or_reconciliation_audit"


def test_below_20_is_length_reject() -> None:
    result = _classify(_s2(sequence=_rna(19), native_id="short"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.primary_route == PRIMARY_ROUTE_REJECT
    assert result.rejection_row is not None
    assert result.rejection_row["rejection_reason"] == "length_out_of_range"
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"


def test_medium_group_proposal_parks_otherwise_valid_record() -> None:
    result = _classify(_s2(sequence=_rna(40)), proposals=[_proposal()])
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason == EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED
    )
    assert result.primary_route == PRIMARY_ROUTE_CONSTRUCT
    assert result.decision["group_covered_by_rule_review"] == "true"
    assert result.decision["review_batch"] == ""
    assert result.decision["manual_review_required"] == "false"
    assert EligibilityReason.CONSTANT_REGION_PROPOSAL in result.eligibility.all_reasons


def test_resolved_construct_review_does_not_repark_group_proposal() -> None:
    canonical = _s2(sequence=_rna(40), native_id="resolvedg")
    result = classify_ena_record(
        canonical,
        _qc(canonical),
        _meta(canonical),
        policy=POLICY,
        proposals=[_proposal()],
        construct_review_resolved=True,
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED not in result.eligibility.all_reasons
    assert EligibilityReason.CONSTANT_REGION_PROPOSAL in result.eligibility.all_reasons


def test_resolved_construct_review_does_not_repark_promoter_concern() -> None:
    canonical = _s2(sequence=_rna(40), native_id="resolvedp")
    result = classify_ena_record(
        canonical,
        _qc(canonical, source_promoter_or_template_concern="true"),
        _meta(canonical),
        policy=POLICY,
        construct_review_resolved=True,
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED not in result.eligibility.all_reasons


def test_source_promoter_without_group_parks() -> None:
    canonical = _s2(sequence=_rna(40), native_id="prom")
    result = _classify(
        canonical,
        qc=_qc(canonical, source_promoter_or_template_concern="true", source_t7_concern="true"),
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason == EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED
    )
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"
    assert result.decision["manual_review_required"] == "true"


def test_length_reject_keeps_trim_concern_secondarily() -> None:
    result = _classify(
        _s2(sequence=_rna(17), native_id="shortg"),
        proposals=[_proposal()],
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED in result.eligibility.secondary_reasons
    assert EligibilityReason.CONSTANT_REGION_PROPOSAL in result.eligibility.secondary_reasons
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"


def test_source_target_type_does_not_route() -> None:
    protein = _classify(
        _s2(sequence=_rna(40), native_id="p"),
        meta=_meta(_s2(sequence=_rna(40), native_id="p"), target_type="protein"),
    )
    ligand = _classify(
        _s2(sequence=_rna(40), native_id="l"),
        meta=_meta(_s2(sequence=_rna(40), native_id="l"), target_type="small_molecule"),
    )
    assert protein.eligibility.proposed_decision == ligand.eligibility.proposed_decision
    assert protein.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert ligand.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert "target_type" not in protein.decision or not protein.decision.get("target_type")


def test_evidence_does_not_route() -> None:
    weak = _classify(
        _s2(sequence=_rna(40), native_id="w"),
        meta=_meta(_s2(sequence=_rna(40), native_id="w"), binding_evidence_strength="weak"),
    )
    none = _classify(
        _s2(sequence=_rna(40), native_id="n"),
        meta=_meta(_s2(sequence=_rna(40), native_id="n"), binding_evidence_strength="none"),
    )
    assert weak.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert none.primary_route == PRIMARY_ROUTE_ELIGIBLE


def test_duplicate_sequence_full_both_remain_and_are_diagnostic() -> None:
    seq = _rna(40)
    a = _s2(sequence=seq, native_id="a")
    b = _s2(sequence=seq, native_id="b")
    ids, n_values, n_records = duplicate_sequence_full_ids([a, b])
    assert n_values == 1
    assert n_records == 2
    assert ids == {"ena:a", "ena:b"}
    classified = [_classify(a), _classify(b)]
    decisions = [row.decision for row in classified]
    local = {row.canonical["record_id"]: {"record_id": row.canonical["record_id"]} for row in classified}
    apply_duplicate_sequence_diagnostic(decisions, local, ids)
    assert all(row["proposed_decision"] == "proposed_accept" for row in decisions)
    assert all(row["exact_sequence_full_duplicate_diagnostic"] == "true" for row in decisions)
    assert all(
        "diagnostic only — no deduplication performed" in row["notes"] for row in decisions
    )


def test_s3_does_not_populate_forbidden_fields() -> None:
    result = _classify(_s2(sequence=_rna(40)))
    for field_name in S3_FORBIDDEN_FIELDS:
        if field_name == "experiment_group_id":
            continue
        assert not result.canonical.get(field_name)
        assert not result.decision.get(field_name)


def test_index_constant_proposals_attaches_by_qc_group() -> None:
    canonical = _s2(sequence=_rna(40), native_id="m1")
    qc = _qc(canonical, experiment_group_id="g9")
    proposal = _proposal(group_id="g9")
    attached = index_constant_proposals([qc], [proposal])
    assert attached[canonical["record_id"]][0]["proposal_id"] == proposal["proposal_id"]


def test_index_constant_proposals_joins_namespaced_s2_group_ids() -> None:
    canonical = _s2(sequence=_rna(40), native_id="m2")
    qc = _qc(canonical, experiment_group_id="experiment_abc")
    proposal = _proposal(group_id="ena:experiment_group:experiment_abc")
    attached = index_constant_proposals([qc], [proposal])
    assert attached[canonical["record_id"]][0]["proposal_id"] == proposal["proposal_id"]


def test_random_audit_excludes_parks_rejects_and_group_covered() -> None:
    accepts = []
    details = {}
    for i in range(3):
        row = _classify(_s2(sequence=_rna(40), native_id=f"ok{i}")).decision
        accepts.append(row)
        details[row["record_id"]] = dict(row)
    park = _classify(_s2(sequence=_rna(40), native_id="park"), proposals=[_proposal()]).decision
    rejects = _classify(_s2(sequence=_rna(19), native_id="rej")).decision
    rows = accepts + [park, rejects]
    take, pool, shortfall = apply_random_accept_audit(
        rows, details, seed=42, sample_size=30
    )
    assert pool == 3
    assert take == 3
    assert shortfall == 27
    assert park["review_batch"] == ""
    assert rejects["review_batch"] == "01_judgement_dependent_technical"
