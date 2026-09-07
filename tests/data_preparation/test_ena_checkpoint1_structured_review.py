"""ENA CHECKPOINT-1 structured review helpers (synthetic sequences only).

Literal nucleotides are short fixtures or repeating ACGU tiles.
Does not read real ENA source sequences.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.ena_checkpoint1_review import (  # noqa: E402
    REC_RETAIN_BOTH,
    build_legacy_collapse_reconciliation,
    build_rule_review_tables,
    populate_record_recommendations,
    validate_ena_review_package,
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def test_one_group_proposal_makes_one_rule_row_not_n_decisions() -> None:
    motif = "ACGUACGU"
    members = []
    canonical = {}
    decisions = {}
    membership = []
    for i in range(4):
        record_id = f"ena:m{i}"
        seq = motif + _rna(32)
        canonical[record_id] = {
            "record_id": record_id,
            "native_id": f"m{i}",
            "sequence_full": seq,
            "sequence_core": seq,
            "sequence_length_full": str(len(seq)),
            "sequence_length_core": str(len(seq)),
            "t_to_u_applied": "false",
        }
        decisions[record_id] = {
            "record_id": record_id,
            "native_id": f"m{i}",
            "source_promoter_or_template_concern": "false",
            "group_covered_by_rule_review": "true",
        }
        membership.append(
            {
                "proposal_id": "g1:five_prime:group_consensus",
                "proposal_source": "group_consensus",
                "record_id": record_id,
            }
        )
        members.append(record_id)
    proposals = [
        {
            "proposal_id": "g1:five_prime:group_consensus",
            "experiment_group_id": "g1",
            "proposal_source": "group_consensus",
            "side": "five_prime",
            "proposed_sequence": motif,
            "motif_length": str(len(motif)),
            "support": "0.75",
            "records_considered": "4",
            "records_matching_exactly": "4",
            "confidence": "medium",
            "applied": "false",
        }
    ]
    rules, member_rows, exceptions = build_rule_review_tables(
        proposals=proposals,
        membership_rows=membership,
        canonical_by_id=canonical,
        decision_by_id=decisions,
    )
    assert len(rules) == 1
    assert len(member_rows) == 4
    assert rules[0]["affected_s3_record_count"] == "4"
    assert rules[0]["side"] == "five_prime"
    assert rules[0]["manual_trim_action"] == ""
    assert rules[0]["manual_notes"] == ""
    assert int(rules[0]["n_hypothetical_exceeds_40pct"]) >= 0
    assert "proposed_sequence" not in rules[0]
    assert all(row["manual_decision"] == "" for row in exceptions)


def test_reconciliation_pair_after_t_to_u_drops_neither_source() -> None:
    rna = _rna(24)
    dna = rna.replace("U", "T")
    canonical_rows = [
        {
            "record_id": "ena:ru_a",
            "native_id": "ru_a",
            "sequence_raw": dna,
            "sequence_full": rna,
            "target_name_raw": "PAP",
        },
        {
            "record_id": "ena:ru_b",
            "native_id": "ru_b",
            "sequence_raw": rna,
            "sequence_full": rna,
            "target_name_raw": "Prostatic acid phosphatase",
        },
    ]
    sidecar_rows = [
        {
            "record_id": "ena:ru_a",
            "review_unit_id": "ru_a",
            "sequence": dna,
            "target": "PAP",
            "manual_sequence_corrected": "",
            "manual_target_corrected": "",
            "sequence_corrected_applied": "0",
            "target_corrected_applied": "0",
        },
        {
            "record_id": "ena:ru_b",
            "review_unit_id": "ru_b",
            "sequence": rna,
            "target": "Prostatic acid phosphatase",
            "manual_sequence_corrected": "",
            "manual_target_corrected": "",
            "sequence_corrected_applied": "0",
            "target_corrected_applied": "0",
        },
    ]
    from finalize_ena_aptamer_supplement import (  # noqa: E402
        canonicalise_target,
        clean_rna_sequence,
        make_clean_record_id,
    )

    clean_seq, _, _ = clean_rna_sequence(dna)
    _, key, _ = canonicalise_target("PAP")
    clean_id = make_clean_record_id(clean_seq, key)
    processed_rows = [
        {
            "clean_record_id": clean_id,
            "internal_duplicate_count": "2",
            "sequence_rna_clean": clean_seq,
        }
    ]
    rows = build_legacy_collapse_reconciliation(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        processed_rows=processed_rows,
        decision_by_id={
            "ena:ru_a": {"group_covered_by_rule_review": "false"},
            "ena:ru_b": {"group_covered_by_rule_review": "false"},
        },
    )
    assert len(rows) == 1
    pair = rows[0]
    assert {pair["record_id_a"], pair["record_id_b"]} == {"ena:ru_a", "ena:ru_b"}
    assert pair["clean_record_id"] == clean_id
    assert pair["legacy_t_to_u"] == "true"
    assert pair["legacy_target_alias"] == "true"
    assert pair["legacy_exact_sequence_target_consolidation"] == "true"
    assert pair["unified_s2_sequence_full_identical"] == "true"
    assert pair["raw_target_name_identical"] == "false"
    assert pair["machine_recommendation"] == REC_RETAIN_BOTH
    assert pair["manual_decision"] == ""
    assert pair["manual_notes"] == ""


def test_non_terminal_match_creates_record_level_exception() -> None:
    motif = "GGGGGGGG"
    seq = "ACGUACGUACGUACGUACGUACGUACGUACGU"
    record_id = "ena:nomatch"
    canonical = {
        record_id: {
            "record_id": record_id,
            "native_id": "nomatch",
            "sequence_full": seq,
            "sequence_core": seq,
            "sequence_length_full": str(len(seq)),
            "sequence_length_core": str(len(seq)),
            "t_to_u_applied": "false",
        }
    }
    decisions = {
        record_id: {
            "record_id": record_id,
            "native_id": "nomatch",
            "source_promoter_or_template_concern": "false",
            "group_covered_by_rule_review": "true",
        }
    }
    proposals = [
        {
            "proposal_id": "g2:five_prime:group_consensus",
            "experiment_group_id": "g2",
            "proposal_source": "group_consensus",
            "side": "five_prime",
            "proposed_sequence": motif,
            "motif_length": str(len(motif)),
            "support": "0.5",
            "records_considered": "1",
            "records_matching_exactly": "0",
            "confidence": "medium",
            "applied": "false",
        }
    ]
    membership = [
        {
            "proposal_id": "g2:five_prime:group_consensus",
            "proposal_source": "group_consensus",
            "record_id": record_id,
        }
    ]
    rules, member_rows, exceptions = build_rule_review_tables(
        proposals=proposals,
        membership_rows=membership,
        canonical_by_id=canonical,
        decision_by_id=decisions,
    )
    assert len(rules) == 1
    assert member_rows[0]["exact_terminal_match"] == "false"
    assert member_rows[0]["hard_invalid"] == "true"
    assert len(exceptions) == 1
    assert "non_terminal_match" in exceptions[0]["exception_reason"]
    assert exceptions[0]["manual_decision"] == ""
    assert rules[0]["machine_recommendation"] == "reject_candidate_trim"


def test_blank_package_fails_closed_and_recommendations_are_not_decisions() -> None:
    queue = [
        populate_record_recommendations(
            {
                "record_id": "ena:1",
                "proposed_decision": "proposed_reject",
                "primary_reason": "length_out_of_range",
                "checkpoint_review_reasons": "judgement_dependent_technical",
                "source_promoter_or_template_concern": "false",
                "manual_decision": "",
                "manual_trim_action": "",
            }
        )
    ]
    rules = [
        {
            "constant_rule_id": "g1:five_prime:group_consensus",
            "machine_recommendation": "needs_source_review",
            "manual_trim_action": "",
            "manual_notes": "",
        }
    ]
    recon = [
        {
            "reconciliation_id": "ena_collapse_01",
            "machine_recommendation": REC_RETAIN_BOTH,
            "manual_decision": "",
            "manual_notes": "",
        }
    ]
    report = validate_ena_review_package(
        queue_rows=queue,
        rule_rows=rules,
        exception_rows=[],
        reconciliation_rows=recon,
    )
    assert report.unresolved_manual_decisions > 0
    assert report.unresolved_constant_rules > 0
    assert report.unresolved_reconciliation_groups > 0
    assert report.ready_for_application == 0
    assert report.ok is False
    assert queue[0]["review_recommendation"]
    assert queue[0]["manual_decision"] == ""
    assert queue[0]["review_recommendation"] != queue[0]["manual_decision"]
